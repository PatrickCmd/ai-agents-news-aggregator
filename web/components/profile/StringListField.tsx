"use client";

import { useFieldArray, useFormContext } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { PlusIcon, XIcon } from "lucide-react";

interface Props {
  name: string;
  label: string;
  placeholder?: string;
}

export function StringListField({ name, label, placeholder = "" }: Props) {
  const { control } = useFormContext();
  const { fields, append, remove } = useFieldArray({ control, name: name as `${string}` });

  return (
    <FormItem>
      <FormLabel>{label}</FormLabel>
      <ul className="space-y-2">
        {fields.map((field, i) => (
          <li key={field.id} className="flex gap-2">
            <FormField
              control={control}
              name={`${name}.${i}` as `${string}`}
              render={({ field: f }) => (
                <FormItem className="flex-1">
                  <Input {...f} placeholder={placeholder} />
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Remove"
              onClick={() => remove(i)}
            >
              <XIcon className="h-4 w-4" />
            </Button>
          </li>
        ))}
      </ul>
      <Button type="button" variant="outline" size="sm" onClick={() => append("")}>
        <PlusIcon className="mr-2 h-4 w-4" />
        Add
      </Button>
    </FormItem>
  );
}
