"""RED→GREEN tests for jscpd duplication ratchet — S3.8 (STRICT TDD, threat-matrix).

Specs: duplication-budget (exit 0/1/2, argv, no shell), ci-workflow-file, pre-commit.
Design D4 + Threat Matrix: shell/subprocess boundary — pinned npx jscpd@4.0.1, tmpdir, no shell=True.
"""

from unittest.mock import MagicMock, patch


def test_jscpd_checker_argv_pins_npx_no_shell():
    """Checker MUST invoke `npx jscpd@4.0.1` as list argv, never shell=True."""
    import scripts.jscpd_check as mod

    captured: list[list[str]] = []

    def fake_run(argv, **kw):
        captured.append(list(argv))
        # Must not use shell=True
        assert kw.get("shell") is not True, "must not use shell=True"
        joined = " ".join(str(x) for x in argv)
        assert "jscpd@4.0.1" in joined, f"argv must pin jscpd@4.0.1, got {argv}"
        assert argv[0] == "npx", f"argv must start with npx, got {argv}"
        assert "json" in joined
        assert "--output" in joined
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m

    # Make _measure_scope use our fake_run indirectly: we patch subprocess.run and let _measure_scope call it
    # To exercise argv, we need to trigger _measure_scope with a real tmpdir that yields a fake report
    # Instead, patch _measure_scope to still call fake_run? Simpler: verify _measure_scope builds the right argv
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal valid report so _measure_scope can parse it after fake_run would have written it
        # But we intercept subprocess.run before it writes — so create the file ourselves
        fake_report = {"statistics": {"total": {"percentage": 1.0, "clones": 0}}}
        import json

        Path(tmpdir, "jscpd-report.json").write_text(json.dumps(fake_report), encoding="utf-8")

        # Call the real _measure_scope but with subprocess.run patched to our fake (which won't overwrite the file)
        # The real _measure_scope will look for rglob *.json and find our pre-written one
        with patch.object(mod.subprocess, "run", side_effect=fake_run):
            pct = mod._measure_scope("bot", tmpdir)
            assert pct == 1.0
        assert captured, "subprocess.run must have been called"
        argv = captured[0]
        assert argv[0] == "npx" and "jscpd@4.0.1" in argv[1], f"argv not pinned: {argv}"
        assert "--reporters" in argv and "json" in argv


def test_jscpd_checker_bad_json_exits_1():
    """Unparsable jscpd report / missing baseline MUST exit 1 (infra)."""
    import scripts.jscpd_check as mod

    # Missing baseline → 1
    with patch.object(mod, "_load_baseline", side_effect=FileNotFoundError("missing baseline")):
        rc = mod.main([])
        assert rc == 1, f"bad baseline must exit 1, got {rc}"

    # Bad JSON after measurement → 1
    with (
        patch.object(mod, "_load_baseline", return_value={"bot": 5.0, "tests": 10.0}),
        patch.object(mod, "_measure_scope", side_effect=ValueError("bad JSON")),
    ):
        rc = mod.main([])
        assert rc == 1, f"bad measure must exit 1, got {rc}"


def test_jscpd_checker_over_ceiling_exits_2():
    """Any scope strictly above its ceiling MUST exit 2 (violation)."""
    import scripts.jscpd_check as mod

    with (
        patch.object(mod, "_load_baseline", return_value={"bot": 2.0, "tests": 5.0}),
        patch.object(mod, "_measure_scope", side_effect=lambda scope, tmpdir: 5.0),  # both over
    ):
        rc = mod.main([])
        assert rc == 2, f"over ceiling must exit 2, got {rc}"

    # One scope over is enough
    with (
        patch.object(mod, "_load_baseline", return_value={"bot": 5.0, "tests": 1.0}),
        patch.object(mod, "_measure_scope", side_effect=lambda scope, tmpdir: 6.0 if scope == "bot" else 1.0),
    ):
        rc = mod.main([])
        assert rc == 2


def test_jscpd_checker_within_ceiling_exits_0():
    """Both scopes at/below ceiling MUST exit 0."""
    import scripts.jscpd_check as mod

    with (
        patch.object(mod, "_load_baseline", return_value={"bot": 5.0, "tests": 10.0}),
        patch.object(mod, "_measure_scope", side_effect=lambda scope, tmpdir: 1.0),
    ):
        rc = mod.main([])
        assert rc == 0, f"within ceiling must exit 0, got {rc}"

    # Equal to ceiling is still pass (not strictly above)
    with (
        patch.object(mod, "_load_baseline", return_value={"bot": 2.1, "tests": 5.0}),
        patch.object(mod, "_measure_scope", side_effect=lambda scope, tmpdir: 2.1 if scope == "bot" else 5.0),
    ):
        rc = mod.main([])
        assert rc == 0, f"equal to ceiling must exit 0, got {rc}"
