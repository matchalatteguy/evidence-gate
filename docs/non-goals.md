# Non-goals

Evidence Gate is intentionally small. It validates local evidence files and emits local review artifacts. The following are outside the current scope.

## Not an experiment tracker

Evidence Gate compares explicitly selected candidate/reference values from local
reports. It does not store run history, select baselines, render dashboards, or manage
metadata databases. Your project owns reference selection and preservation.

## Not a hosted service

There is no server, queue, worker, web UI, account system, or API service. The CLI reads and writes local files.

## Not an artifact store or data lake

Evidence Gate checks declared files, optional fingerprints, and configured CSV
content/counts/types/ranges. It does not upload, copy, version, deduplicate, or
warehouse artifacts, or validate arbitrary JSON Schemas or CSV key uniqueness.

## Not a scheduler

Evidence Gate does not start pipeline jobs or retry failed work. Run your pipeline first, then validate the evidence it produced.

## Not a replacement for review

A passing validation result means the run satisfied the configured contract. It does not prove that the underlying model, dataset, benchmark, or document output is correct or useful. Humans and project-specific reviewers still own final decisions.

## No live external integrations

Evidence Gate does not manage credentials, call hosted APIs, perform authenticated workflows, mutate remote state, or require network access for validation.

## No private or machine-specific assumptions

Contracts and examples should use synthetic data and relative paths. Do not put secrets, usernames, hostnames, absolute local paths, or private project details in specs, report files, examples, or docs.
