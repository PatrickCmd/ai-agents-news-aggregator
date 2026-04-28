import { StringListField } from "./StringListField";

export function BackgroundFieldArray() {
  return (
    <StringListField
      name="background"
      label="Background"
      placeholder="e.g. AI engineer, Backend dev"
    />
  );
}
