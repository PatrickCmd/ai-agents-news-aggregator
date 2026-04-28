import { StringListField } from "./StringListField";

export function PreferencesFieldGroup() {
  return (
    <fieldset className="space-y-4">
      <legend className="font-semibold">Preferences</legend>
      <StringListField
        name="preferences.content_type"
        label="Content type"
        placeholder="Technical deep dives, paper summaries"
      />
      <StringListField
        name="preferences.avoid"
        label="Avoid"
        placeholder="Press releases, marketing posts"
      />
    </fieldset>
  );
}
