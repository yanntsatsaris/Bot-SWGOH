---
trigger: always_on
description: Response language contract and the fixed French vocabulary for this repository
---

# Language

**Answer in the language of the question.** A question asked in French gets an answer
entirely in French — section headings, table headers, bullet labels and summaries
included. This is not a preference; it is the contract with the person reading you.

Instruction files in this repository are written in English on purpose: they are
instructions addressed to you, not text to reproduce. **Reading English does not make
you answer in English.** This is the single most common failure, and it happens exactly
when you have just loaded a skill or rule — be deliberate at that moment.

## Specific failures to avoid

- Answering in English after reading an English skill, rule or agent file.
- French prose under English headings copied from the file you just read.
- Quoting a rule verbatim at the user instead of applying it and explaining the outcome
  in their language.
- Half-translating: a French sentence with an English clause spliced in.
- Inventing a new French word for a concept you already translated differently earlier in
  the session. Use the table below.

## Never translate

Code identifiers · function, variable and class names · French comments already in the
code · file names and paths · branch names · commit-message prefixes (`feat:`, `fix:`,
`chore:`) · library and tool names · command-line flags · raw tool output (`pytest`,
`git`, tracebacks). Quote tool output verbatim and explain it in the user's language.

**Commit messages stay in English** — every commit in this repository's history is
English, and a bilingual log is worse than either language alone. Pull request titles and
descriptions follow the reader.

## Fixed vocabulary

Same concept, same French word, every time.

| English | Français |
|---|---|
| shadowed definition | définition masquée |
| ratchet | cliquet |
| round trip | aller-retour |
| layering | découpage en couches |
| test floor | plancher de tests |
| coverage | couverture |
| guard | garde-fou |
| fallback | repli |
| to pin (a dependency) | épingler |
| subagent | sous-agent |
| slash command | commande slash |
| ally code | code allié |
| fleet | flotte |
| squad | équipe |
| defence | défense |

Left in English because they are the domain's own words: cog, hook, prompt, quota,
scraping, roster, counter, bracket, commit, branch, merge, rebase.
