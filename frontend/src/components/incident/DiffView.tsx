"use client";

import { useMemo } from "react";
import { cx } from "@/components/ui";
import type { FileChange } from "@/lib/types";

type Kind = "add" | "del" | "ctx" | "hunk";
export type DiffLine = { kind: Kind; text: string; oldNo?: number; newNo?: number };
export type DiffFile = { path: string; lines: DiffLine[] };

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

/** Minimal unified-diff parser: enough for `git diff` output, ignores binary and rename metadata. */
export function parseDiff(diff: string): DiffFile[] {
  const files: DiffFile[] = [];
  let file: DiffFile | null = null;
  let oldNo = 0;
  let newNo = 0;
  let inHunk = false;

  const open = (path: string): DiffFile => {
    const next: DiffFile = { path, lines: [] };
    inHunk = false;
    files.push(next);
    return next;
  };

  const raws = diff.split("\n");
  if (raws.at(-1) === "") raws.pop(); // the trailing newline is not a context line

  for (const raw of raws) {
    if (raw.startsWith("diff --git")) {
      file = open(raw.split(" b/").at(-1) ?? raw.slice(11));
      continue;
    }
    if (raw.startsWith("+++ ")) {
      const path = raw.slice(4).replace(/^b\//, "").trim();
      if (!file) file = open(path);
      else if (path && path !== "/dev/null") file.path = path;
      continue;
    }
    if (raw.startsWith("--- ")) continue;
    const hunk = HUNK.exec(raw);
    if (hunk) {
      if (!file) file = open("changed file");
      oldNo = Number(hunk[1]);
      newNo = Number(hunk[2]);
      inHunk = true;
      file?.lines.push({ kind: "hunk", text: raw });
      continue;
    }
    if (!file || !inHunk) continue;
    if (raw.startsWith("\\")) continue; // "\ No newline at end of file"
    if (raw.startsWith("+")) file.lines.push({ kind: "add", text: raw.slice(1), newNo: newNo++ });
    else if (raw.startsWith("-")) file.lines.push({ kind: "del", text: raw.slice(1), oldNo: oldNo++ });
    else file.lines.push({ kind: "ctx", text: raw.slice(1), oldNo: oldNo++, newNo: newNo++ });
  }
  return files;
}

function splitRows(lines: DiffLine[]): { left: DiffLine | null; right: DiffLine | null }[] {
  const rows: { left: DiffLine | null; right: DiffLine | null }[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.kind === "hunk" || line.kind === "ctx") {
      rows.push({ left: line, right: line });
      i += 1;
      continue;
    }
    const removed: DiffLine[] = [];
    const added: DiffLine[] = [];
    while (i < lines.length && lines[i].kind === "del") removed.push(lines[i++]);
    while (i < lines.length && lines[i].kind === "add") added.push(lines[i++]);
    for (let k = 0; k < Math.max(removed.length, added.length); k += 1) {
      rows.push({ left: removed[k] ?? null, right: added[k] ?? null });
    }
  }
  return rows;
}

const ROW_TONE: Record<Kind, string> = {
  add: "bg-ok-bg",
  del: "bg-bad-bg",
  ctx: "",
  hunk: "bg-surface-2 text-text-3",
};
const MARK: Record<Kind, string> = { add: "+", del: "-", ctx: " ", hunk: "" };
const MARK_TONE: Record<Kind, string> = { add: "text-ok", del: "text-bad", ctx: "text-text-3", hunk: "text-text-3" };

function Gutter({ n }: { n?: number }) {
  return (
    <span aria-hidden className="w-9 shrink-0 select-none pr-2 text-right text-text-3">
      {n ?? ""}
    </span>
  );
}

function Row({ line, side }: { line: DiffLine | null; side?: "old" | "new" }) {
  if (!line) return <div className="bg-surface-2/60">&nbsp;</div>;
  return (
    <div className={cx("flex items-baseline", ROW_TONE[line.kind])}>
      {side === undefined ? (
        <>
          <Gutter n={line.oldNo} />
          <Gutter n={line.newNo} />
        </>
      ) : (
        <Gutter n={side === "old" ? line.oldNo : line.newNo} />
      )}
      <span className={cx("w-3 shrink-0 select-none", MARK_TONE[line.kind])} aria-hidden>
        {MARK[line.kind]}
      </span>
      <span className={cx("whitespace-pre pr-4", line.kind === "hunk" ? "text-text-3" : "text-text")}>
        {line.text || " "}
      </span>
    </div>
  );
}

function UnifiedBody({ lines }: { lines: DiffLine[] }) {
  return (
    <div className="scroll-quiet overflow-x-auto py-1">
      <div className="min-w-max">
        {lines.map((line, i) => (
          <Row key={i} line={line} />
        ))}
      </div>
    </div>
  );
}

/** Side by side over the same hunks. Each column scrolls on its own so both halves stay in view. */
function SplitBody({ lines }: { lines: DiffLine[] }) {
  const rows = useMemo(() => splitRows(lines), [lines]);
  const column = (side: "old" | "new") => (
    <div className={cx("scroll-quiet min-w-0 flex-1 overflow-x-auto py-1", side === "old" && "border-r border-line")}>
      <div className="min-w-max">
        {rows.map((row, i) => (
          <Row key={i} line={side === "old" ? row.left : row.right} side={side} />
        ))}
      </div>
    </div>
  );
  return (
    <div className="flex w-full">
      {column("old")}
      {column("new")}
    </div>
  );
}

/** Unified diff renderer. `counts` come from the proposal so the header matches the server. */
export function DiffView({
  diff,
  counts,
  view,
}: {
  diff: string;
  counts: FileChange[];
  view: "unified" | "split";
}) {
  const files = useMemo(() => parseDiff(diff), [diff]);
  const countOf = new Map(counts.map((c) => [c.path, c]));
  if (!files.length) {
    return <p className="text-[12px] text-text-3">The proposal carries no diff.</p>;
  }
  return (
    <div className="space-y-3">
      {files.map((file) => {
        const count = countOf.get(file.path);
        const additions = count?.additions ?? file.lines.filter((l) => l.kind === "add").length;
        const deletions = count?.deletions ?? file.lines.filter((l) => l.kind === "del").length;
        return (
          <div key={file.path} className="overflow-hidden rounded-control border border-line">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-surface-2 px-3 py-1.5">
              <span className="num min-w-0 break-all text-[12px] text-text">{file.path}</span>
              <span className="num ml-auto text-[11px] tnum">
                <span className="text-ok">+{additions}</span> <span className="text-bad">-{deletions}</span>
              </span>
            </div>
            <div className="bg-surface font-mono text-[12px] leading-[1.6]">
              {view === "unified" ? <UnifiedBody lines={file.lines} /> : <SplitBody lines={file.lines} />}
            </div>
          </div>
        );
      })}
    </div>
  );
}
