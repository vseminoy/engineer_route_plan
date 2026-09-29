import { z } from 'zod';
import type { FieldErrors, ValidationError } from '@/api/generated/schemas';

// One message per form field, however it was found: a failed zod parse of the
// form's own input, or the `fields` of a backend 400 response. Forms read only
// this shape, so the two sources render identically.
export type FieldErrorMap = Record<string, string>;

export function isFieldErrors(body: ValidationError): body is FieldErrors {
  return 'fields' in body;
}

// zod's issue path (`['engineers', 2, 'skills']`) becomes the same dotted/bracket
// name the spec (and the backend's `fields[].name`) uses: `engineers[2].skills`.
export function fieldErrorsFromZod(error: z.ZodError): FieldErrorMap {
  const map: FieldErrorMap = {};
  for (const issue of error.issues) {
    map[z.core.toDotPath(issue.path)] = issue.message;
  }
  return map;
}

export function fieldErrorsFromApi(body: FieldErrors): FieldErrorMap {
  const map: FieldErrorMap = {};
  for (const field of body.fields) {
    map[field.name] = field.message;
  }
  return map;
}
