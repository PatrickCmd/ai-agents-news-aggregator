import { StringListField } from "./StringListField";

export function GoalsFieldArray() {
  return (
    <StringListField
      name="goals"
      label="Goals"
      placeholder="Stay current on agent infra"
    />
  );
}
