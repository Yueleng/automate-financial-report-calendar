"use client";

import { getSymbolColor } from "@/lib/colors";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { CheckIcon } from "lucide-react";

interface SymbolFilterProps {
  symbols: string[];
  selectedSymbols: string[];
  counts?: Record<string, number>;
  onChange: (selected: string[]) => void;
}

export function SymbolFilter({
  symbols,
  selectedSymbols,
  counts,
  onChange,
}: SymbolFilterProps) {
  if (symbols.length === 0) return null;

  const allSelected = selectedSymbols.length === symbols.length;
  const noneSelected = selectedSymbols.length === 0;

  const selectAll = () => onChange([...symbols]);
  const clearAll = () => onChange([]);

  return (
    <div className="flex flex-wrap items-center gap-2 py-2">
      <div className="flex items-center gap-1.5 mr-2">
        <span className="text-xs font-medium text-muted-foreground">
          Filter:
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={selectAll}
          disabled={allSelected}
          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
        >
          All
        </Button>
        <span className="text-zinc-600">/</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={clearAll}
          disabled={noneSelected}
          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
        >
          None
        </Button>
      </div>

      <ToggleGroup
        type="multiple"
        value={selectedSymbols}
        onValueChange={onChange}
        spacing={1.5}
        className="flex-wrap"
        aria-label="Filter calendar by symbol"
      >
        {symbols.map((sym) => {
          const isSelected = selectedSymbols.includes(sym);
          const color = getSymbolColor(sym);
          const count = counts?.[sym];

          return (
            <ToggleGroupItem
              key={sym}
              value={sym}
              className={`h-auto min-w-0 gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-all duration-150 ${
                isSelected
                  ? "shadow-sm opacity-100"
                  : "opacity-40 hover:opacity-75 border-zinc-700 bg-card/40 text-muted-foreground"
              }`}
              style={
                isSelected
                  ? {
                      backgroundColor: color.bg,
                      borderColor: color.border,
                      color: color.text,
                    }
                  : undefined
              }
            >
              {isSelected && <CheckIcon className="w-3 h-3 stroke-[2.5]" />}
              <span>{sym}</span>
              {count !== undefined && (
                <span className="text-[10px] opacity-75 font-mono">
                  ({count})
                </span>
              )}
            </ToggleGroupItem>
          );
        })}
      </ToggleGroup>
    </div>
  );
}
