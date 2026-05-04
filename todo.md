# TODO

## Before publication (in this repo)

- [ ] End-to-end reproduction check — run steps 3–6 against committed inputs and diff `outputs/ec3/` against committed versions

## When moving to the final public repo (`github.com/stefan-1992/ACC-function-generation`)

- [ ] Ship IFC data so reviewers can reproduce end-to-end:
  - `acc/bim_models/<name>/*.ifc` + `*.smc` + per-model rule/classification files — currently gitignored (`acc/bim_models` in `.gitignore`, `*.ifc` globally ignored)
  - `acc/res/<name>/bcfzip/*` — currently gitignored (`acc/res/*/bcfzip`)
  - `acc/res/<name>/smc/*` — currently gitignored (`acc/res/*/smc`)
  - Keep `acc/res/<name>/temp/` ignored (intermediate)
  - Licences: the 3 course-sourced models (146, 106, 172) and the IFCBench models retain their original licences.
