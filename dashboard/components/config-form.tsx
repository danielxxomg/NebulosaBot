"use client";

import { useTransition, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ActionResult } from "@/lib/types";

/**
 * Field types the ConfigForm can render.
 *
 * Note: "select" is intentionally excluded — the Base UI Select
 * component does not support native form submission. Use "text" with
 * server-side validation for constrained values (e.g., language codes).
 */
export type ConfigFieldType = "text" | "number" | "textarea" | "switch";

/**
 * Descriptor for a single config field in the form.
 */
export interface ConfigField {
  /** form field name (used as the FormData key). */
  name: string;
  /** Label displayed above the field. */
  label: string;
  /** Input type. */
  type: ConfigFieldType;
  /** Default value (string for text/number/textarea, boolean for switch). */
  defaultValue?: string | number | boolean;
  /** Placeholder text (ignored for switch). */
  placeholder?: string;
  /** Hint text shown below the field. */
  hint?: string;
  /** Whether the field is required to have a value. */
  required?: boolean;
}

/**
 * Props for the ConfigForm component.
 */
export interface ConfigFormProps {
  /** The Supabase guild ID (passed to the Server Action). */
  guildId: string;
  /** Server Action that persists the form data. */
  action: (guildId: string, formData: FormData) => Promise<ActionResult>;
  /** Fields to render in the form. */
  fields: ConfigField[];
  /** Card title. */
  title?: string;
  /** Card description / subtitle. */
  description?: string;
}

/**
 * Reusable configuration form with Server Action integration.
 *
 * Renders fields based on a declarative `ConfigField[]` array,
 * handles submission via `useTransition`, and displays per-field
 * validation errors alongside a success banner.
 */
export function ConfigForm({
  guildId,
  action,
  fields,
  title,
  description,
}: ConfigFormProps) {
  const [isPending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionResult | null>(null);

  function handleSubmit(formData: FormData) {
    setResult(null);
    startTransition(async () => {
      const res = await action(guildId, formData);
      setResult(res);
    });
  }

  return (
    <Card>
      {(title || description) && (
        <CardHeader>
          {title && <CardTitle>{title}</CardTitle>}
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
      )}
      <CardContent>
        {/* Success banner */}
        {result?.success && (
          <div className="mb-4 rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 text-sm text-green-600 dark:text-green-400">
            {result.message}
          </div>
        )}

        {/* Global error (no field) */}
        {result && !result.success && !("field" in result) && (
          <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {result.error}
          </div>
        )}

        <form action={handleSubmit} className="space-y-5">
          {fields.map((field) => {
            const fieldError =
              result && !result.success && "field" in result && result.field === field.name
                ? result.error
                : null;

            return (
              <div key={field.name} className="space-y-1.5">
                {/* Label row */}
                <div className="flex items-center justify-between">
                  <Label
                    htmlFor={field.name}
                    className={cn(fieldError && "text-destructive")}
                  >
                    {field.label}
                    {field.required && <span className="ml-0.5 text-destructive">*</span>}
                  </Label>

                  {/* Switch field: render the Switch inline next to the label */}
                  {field.type === "switch" && (
                    <Switch
                      id={field.name}
                      name={field.name}
                      defaultChecked={field.defaultValue === true}
                      aria-invalid={!!fieldError}
                    />
                  )}
                </div>

                {/* Non-switch input fields */}
                {field.type === "text" && (
                  <Input
                    id={field.name}
                    name={field.name}
                    type="text"
                    defaultValue={String(field.defaultValue ?? "")}
                    placeholder={field.placeholder}
                    aria-invalid={!!fieldError}
                  />
                )}

                {field.type === "number" && (
                  <Input
                    id={field.name}
                    name={field.name}
                    type="number"
                    defaultValue={String(field.defaultValue ?? "")}
                    placeholder={field.placeholder}
                    aria-invalid={!!fieldError}
                  />
                )}

                {field.type === "textarea" && (
                  <textarea
                    id={field.name}
                    name={field.name}
                    defaultValue={String(field.defaultValue ?? "")}
                    placeholder={field.placeholder}
                    rows={4}
                    className={cn(
                      "flex w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-base transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/30",
                      fieldError && "border-destructive ring-3 ring-destructive/20 dark:border-destructive/50 dark:ring-destructive/40"
                    )}
                    aria-invalid={!!fieldError}
                  />
                )}

                {/* Hint text */}
                {field.hint && !fieldError && (
                  <p className="text-xs text-muted-foreground">{field.hint}</p>
                )}

                {/* Field error */}
                {fieldError && (
                  <p className="text-xs text-destructive">{fieldError}</p>
                )}
              </div>
            );
          })}

          <Button type="submit" disabled={isPending} className="w-full sm:w-auto">
            {isPending ? "Saving..." : "Save Changes"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
