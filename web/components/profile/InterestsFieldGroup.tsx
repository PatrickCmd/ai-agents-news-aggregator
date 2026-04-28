import { StringListField } from "./StringListField";

export function InterestsFieldGroup() {
  return (
    <fieldset className="space-y-4">
      <legend className="font-semibold">Interests</legend>
      <StringListField name="interests.primary" label="Primary" placeholder="LLMs, agents" />
      <StringListField name="interests.secondary" label="Secondary" placeholder="devops, security" />
      <StringListField
        name="interests.specific_topics"
        label="Specific topics"
        placeholder="MCP servers, RAG"
      />
    </fieldset>
  );
}
