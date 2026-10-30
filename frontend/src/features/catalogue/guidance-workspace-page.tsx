import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-context";

export function GuidanceWorkspacePage() {
  const cache = useQueryClient();
  const { user } = useAuth();
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [guidanceQuestion, setGuidanceQuestion] = useState("");
  const [searchRequested, setSearchRequested] = useState(false);
  const [selectedMapping, setSelectedMapping] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [ingestion, setIngestion] = useState({
    source_version_id: "",
    document_id: "",
    document_version_id: "",
  });
  const [source, setSource] = useState({
    key: "",
    title: "",
    version_label: "demo-1.0",
    source_type: "DEMONSTRATION_GUIDANCE",
  });
  const [requirement, setRequirement] = useState({
    stable_identifier: "",
    source_version_id: "",
    title: "",
    description: "",
    category: "APPLICATION_DOCUMENTATION",
    module_key: "APPLICATION",
  });
  const [mapping, setMapping] = useState({
    requirement_id: "",
    application_id: "",
    document_id: "",
    document_version_id: "",
    explanation: "",
  });
  const sources = useQuery({
    queryKey: ["guidance-sources"],
    queryFn: api.guidanceSources,
  });
  const requirements = useQuery({
    queryKey: ["catalogue-requirements"],
    queryFn: () => api.catalogueRequirements(),
  });
  const mappings = useQuery({
    queryKey: ["requirement-mappings"],
    queryFn: () => api.requirementMappings(),
  });
  const guidanceSearch = useQuery({
    queryKey: ["guidance-search", guidanceQuestion],
    queryFn: () => api.guidanceSearch(guidanceQuestion),
    enabled: searchRequested && Boolean(guidanceQuestion.trim()),
  });
  const history = useQuery({
    queryKey: ["requirement-mapping-history", selectedMapping],
    queryFn: () => api.requirementMappingHistory(selectedMapping ?? ""),
    enabled: Boolean(selectedMapping),
  });
  const runs = useQuery({
    queryKey: ["guidance-ingestions", ingestion.source_version_id],
    queryFn: () => api.guidanceIngestions(ingestion.source_version_id),
    enabled: Boolean(ingestion.source_version_id),
  });
  const run = useQuery({
    queryKey: ["guidance-extraction-run", selectedRun],
    queryFn: () => api.guidanceExtractionRun(selectedRun ?? ""),
    enabled: Boolean(selectedRun),
  });
  const canManage = Boolean(user?.permissions.includes("guidance.manage"));
  const canReview = Boolean(user?.permissions.includes("guidance.review"));
  const canPropose = Boolean(user?.permissions.includes("mapping.propose"));
  const canReviewMappings = Boolean(
    user?.permissions.includes("mapping.review"),
  );
  const canIngest = Boolean(user?.permissions.includes("guidance.ingest"));
  const canReviewExtraction = Boolean(
    user?.permissions.includes("guidance.extract.review"),
  );
  const visible = useMemo(
    () =>
      (requirements.data ?? []).filter((item) =>
        `${item.stable_identifier} ${item.title} ${item.category}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [requirements.data, search],
  );
  const refresh = () => {
    void cache.invalidateQueries({ queryKey: ["guidance-sources"] });
    void cache.invalidateQueries({ queryKey: ["catalogue-requirements"] });
    void cache.invalidateQueries({ queryKey: ["requirement-mappings"] });
    void cache.invalidateQueries({ queryKey: ["guidance-ingestions"] });
    void cache.invalidateQueries({ queryKey: ["guidance-extraction-run"] });
  };
  const command = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      setNotice("Saved successfully.");
      refresh();
    },
    onError: (error) =>
      setNotice(
        error instanceof ApiError
          ? error.message
          : "The request could not be completed.",
      ),
  });
  const action = (
    id: string,
    kind: "guidance" | "requirement" | "mapping",
    value: string,
    reasonRequired = false,
  ) => {
    const reason = reasonRequired
      ? window.prompt("Reason (required)")
      : undefined;
    if (reasonRequired && !reason?.trim()) return;
    const fn =
      kind === "guidance"
        ? () => api.guidanceVersionAction(id, value, reason ?? undefined)
        : kind === "requirement"
          ? () => api.catalogueRequirementAction(id, value, reason ?? undefined)
          : () => api.requirementMappingAction(id, value, reason ?? undefined);
    command.mutate(fn);
  };
  if (sources.isLoading || requirements.isLoading || mappings.isLoading)
    return <Card>Loading guidance catalogue…</Card>;
  if (sources.isError || requirements.isError || mappings.isError)
    return (
      <Alert>
        <div>
          Unable to load the guidance catalogue.
          <Button
            className="ml-2"
            variant="outline"
            onClick={() => {
              void sources.refetch();
              void requirements.refetch();
              void mappings.refetch();
            }}
          >
            Retry
          </Button>
        </div>
      </Alert>
    );
  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Guidance and evidence catalogue</h1>
        <p className="page-description">
          Human-reviewed source provenance and exact private-document mappings.
          Synthetic material is not official AICTE guidance.
        </p>
      </div>
      {notice ? <Alert>{notice}</Alert> : null}
      <Card>
        <h2 className="font-semibold">Approved guidance search</h2>
        <p className="mt-1 text-sm text-muted">Only approved, page-provenanced extraction is searched. The active retrieval mode is shown with each result.</p>
        <div className="mt-3 flex gap-2"><Input value={guidanceQuestion} onChange={(event) => { setGuidanceQuestion(event.target.value); setSearchRequested(false); }} placeholder="Ask about approved guidance" aria-label="Guidance search" /><Button disabled={!guidanceQuestion.trim()} onClick={() => setSearchRequested(true)}>Search</Button></div>
        {guidanceSearch.isLoading ? <p className="mt-3 text-sm text-muted">Searching authorized passages…</p> : null}
        {guidanceSearch.isError ? <Alert className="mt-3">Guidance search failed or access to its private source is unavailable.</Alert> : null}
        {guidanceSearch.data ? <div className="mt-3 space-y-2"><p className="text-xs text-muted">Mode: {guidanceSearch.data.mode}</p>{guidanceSearch.data.results.map((result) => <div className="rounded border p-3 text-sm" key={result.passage_id}><Badge tone={result.verification_status === "VERIFIED_OFFICIAL" ? "success" : "warning"}>{result.verification_status === "VERIFIED_OFFICIAL" ? "Verified official" : "Synthetic demo"}</Badge><p className="mt-2 whitespace-pre-wrap">{result.text}</p><p className="mt-2 text-xs text-muted">Source version {result.source_version_id} · page {result.page_number} · {result.relevance_method}</p></div>)}{guidanceSearch.data.results.length === 0 ? <p className="text-sm text-muted">No authorized relevant passage was found.</p> : null}</div> : null}
      </Card>
      <Card>
        <h2 className="font-semibold">Guidance sources</h2>
        <div className="mt-3 space-y-3">
          {sources.data?.map((item) => (
            <div className="rounded border p-3" key={item.id}>
              <p className="font-medium">
                {item.title}{" "}
                <span className="text-xs text-muted">{item.key}</span>
              </p>
              {item.versions.map((version) => (
                <div
                  className="mt-2 flex flex-wrap items-center gap-2 text-sm"
                  key={version.id}
                >
                  <Badge
                    tone={
                      version.verification_status === "VERIFIED_OFFICIAL"
                        ? "success"
                        : "warning"
                    }
                  >
                    {version.verification_status === "VERIFIED_OFFICIAL"
                      ? "Verified official"
                      : "Synthetic demo"}
                  </Badge>
                  <Badge
                    tone={version.status === "APPROVED" ? "success" : "info"}
                  >
                    {version.status}
                  </Badge>
                  <span>
                    v{version.version_number} · {version.version_label}
                  </span>
                  {canManage && version.status === "DRAFT" ? (
                    <Button
                      variant="outline"
                      onClick={() => action(version.id, "guidance", "submit")}
                    >
                      Submit
                    </Button>
                  ) : null}
                  {canReview && version.status === "SUBMITTED" ? (
                    <Button
                      onClick={() => action(version.id, "guidance", "approve")}
                    >
                      Approve
                    </Button>
                  ) : null}
                  {canReview && version.status === "APPROVED" ? (
                    <Button
                      variant="outline"
                      onClick={() =>
                        action(version.id, "guidance", "archive", true)
                      }
                    >
                      Archive
                    </Button>
                  ) : null}
                </div>
              ))}
            </div>
          ))}
          {sources.data?.length === 0 ? (
            <p className="text-sm text-muted">
              No authorized guidance sources.
            </p>
          ) : null}
        </div>
        {canManage ? (
          <div className="mt-4 border-t pt-4">
            <h3 className="font-medium">Create source metadata</h3>
            <div className="mt-2 grid gap-2 sm:grid-cols-4">
              <Input
                value={source.key}
                onChange={(event) =>
                  setSource({
                    ...source,
                    key: event.target.value.toUpperCase(),
                  })
                }
                placeholder="SOURCE_KEY"
                aria-label="Source key"
              />
              <Input
                value={source.title}
                onChange={(event) =>
                  setSource({ ...source, title: event.target.value })
                }
                placeholder="Source title"
                aria-label="Source title"
              />
              <Input
                value={source.version_label}
                onChange={(event) =>
                  setSource({ ...source, version_label: event.target.value })
                }
                placeholder="Version label"
                aria-label="Version label"
              />
              <select
                value={source.source_type}
                onChange={(event) =>
                  setSource({ ...source, source_type: event.target.value })
                }
                className="rounded border px-3 text-sm"
                aria-label="Source type"
              >
                <option value="DEMONSTRATION_GUIDANCE">Synthetic demo</option>
                <option value="OFFICIAL_REFERENCE">Official reference</option>
              </select>
            </div>
            <Button
              className="mt-2"
              disabled={
                command.isPending || !source.key || source.title.length < 2
              }
              onClick={() =>
                command.mutate(() =>
                  api.createGuidanceSource({
                    ...source,
                    verification_status:
                      source.source_type === "OFFICIAL_REFERENCE"
                        ? "VERIFIED_OFFICIAL"
                        : "SYNTHETIC_DEMONSTRATION",
                  }),
                )
              }
            >
              Create draft source
            </Button>
          </div>
        ) : null}
      </Card>
      {canIngest || selectedRun ? (
        <Card>
          <h2 className="font-semibold">Secure document ingestion</h2>
          <p className="mt-1 text-sm text-muted">
            Extraction is linked to one immutable private document version. Text
            remains a review aid until a human approves the run.
          </p>
          {canIngest ? (
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <Input value={ingestion.source_version_id} onChange={(event) => setIngestion({ ...ingestion, source_version_id: event.target.value })} placeholder="Guidance version UUID" aria-label="Guidance version UUID" />
              <Input value={ingestion.document_id} onChange={(event) => setIngestion({ ...ingestion, document_id: event.target.value })} placeholder="Private document UUID" aria-label="Private document UUID" />
              <Input value={ingestion.document_version_id} onChange={(event) => setIngestion({ ...ingestion, document_version_id: event.target.value })} placeholder="Exact document version UUID" aria-label="Document version UUID" />
            </div>
          ) : null}
          {canIngest ? <Button className="mt-2" disabled={command.isPending || Object.values(ingestion).some((value) => value.length < 2)} onClick={() => command.mutate(() => api.startGuidanceIngestion(ingestion.source_version_id, { document_id: ingestion.document_id, document_version_id: ingestion.document_version_id, synchronous: true }).then((item) => { setSelectedRun(item.id); }))}>Extract now</Button> : null}
          {runs.isLoading ? <p className="mt-3 text-sm text-muted">Loading extraction history…</p> : null}
          {runs.isError ? <Alert className="mt-3">Unable to load extraction history. <Button variant="outline" onClick={() => void runs.refetch()}>Retry</Button></Alert> : null}
          <div className="mt-3 space-y-2">
            {runs.data?.map((item) => <button type="button" className="block w-full rounded border p-3 text-left text-sm hover:bg-muted" key={item.id} onClick={() => setSelectedRun(item.id)}><span className="font-medium">Attempt {item.attempt_number}</span> · {item.status} · {item.review_status}{item.failure_category ? ` · ${item.failure_category}` : ""}</button>)}
          </div>
          {run.isLoading ? <p className="mt-3 text-sm text-muted">Loading protected extraction…</p> : null}
          {run.isError ? <Alert className="mt-3">Unable to load this extraction. You may not be authorized for its private source document.</Alert> : null}
          {run.data ? <div className="mt-3 space-y-3 border-t pt-3"><div className="flex flex-wrap gap-2"><Badge tone={run.data.status === "APPROVED_FOR_USE" ? "success" : "warning"}>{run.data.status}</Badge>{canReviewExtraction && run.data.status === "NEEDS_REVIEW" ? <><Button onClick={() => command.mutate(() => api.reviewGuidanceExtraction(run.data!.id, "approve"))}>Approve extraction</Button><Button variant="outline" onClick={() => { const reason = window.prompt("Rejection reason (required)"); if (reason?.trim()) command.mutate(() => api.reviewGuidanceExtraction(run.data!.id, "reject", reason)); }}>Reject</Button></> : null}</div>{run.data.warnings.length ? <p className="text-sm text-muted">Warnings: {run.data.warnings.join(", ")}</p> : null}{run.data.pages?.map((page) => <div className="rounded border p-3 text-sm" key={page.id}><p className="font-medium">Page {page.page_number} · {page.method}</p><pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs">{page.corrected_text ?? page.raw_text}</pre>{canReviewExtraction ? <Button className="mt-2" variant="outline" onClick={() => { const corrected = window.prompt("Corrected text", page.corrected_text ?? page.raw_text); const reason = window.prompt("Correction reason (required)"); if (corrected?.trim() && reason?.trim()) command.mutate(() => api.correctGuidanceExtraction(page.id, corrected, reason)); }}>Correct transcription</Button> : null}</div>)}</div> : null}
        </Card>
      ) : null}
      <Card>
        <h2 className="font-semibold">Requirement catalogue</h2>
        <Input
          className="mt-3"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search requirements"
          aria-label="Search requirements"
        />
        <div className="mt-3 space-y-2">
          {visible.map((item) => (
            <div className="rounded border p-3" key={item.id}>
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium">
                  {item.stable_identifier} v{item.version_number} · {item.title}
                </span>
                <Badge tone={item.status === "APPROVED" ? "success" : "info"}>
                  {item.status}
                </Badge>
              </div>
              <p className="text-sm text-muted">
                {item.category} · {item.module_key} · source version {item.source_version_id}{" "}
                {item.section_reference ? `· ${item.section_reference}` : ""}
              </p>
              <p className="text-xs text-muted">
                {item.reviewed_at
                  ? `Reviewed ${new Date(item.reviewed_at).toLocaleString()}`
                  : "Draft provenance; not an official obligation."}
              </p>
              <p className="mt-1 text-sm">{item.description}</p>
              {canManage && item.status === "DRAFT" ? (
                <Button
                  className="mt-2"
                  variant="outline"
                  onClick={() => action(item.id, "requirement", "submit")}
                >
                  Submit
                </Button>
              ) : null}
              {canReview && item.status === "SUBMITTED" ? (
                <Button
                  className="mt-2"
                  onClick={() => action(item.id, "requirement", "approve")}
                >
                  Approve
                </Button>
              ) : null}
            </div>
          ))}
          {visible.length === 0 ? (
            <p className="text-sm text-muted">No matching requirements.</p>
          ) : null}
        </div>
        {canManage ? (
          <div className="mt-4 border-t pt-4">
            <h3 className="font-medium">Create draft requirement</h3>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              <Input
                value={requirement.stable_identifier}
                onChange={(event) =>
                  setRequirement({
                    ...requirement,
                    stable_identifier: event.target.value.toUpperCase(),
                  })
                }
                placeholder="REQUIREMENT.ID"
                aria-label="Requirement identifier"
              />
              <Input
                value={requirement.source_version_id}
                onChange={(event) =>
                  setRequirement({
                    ...requirement,
                    source_version_id: event.target.value,
                  })
                }
                placeholder="Approved source version UUID"
                aria-label="Source version UUID"
              />
              <Input
                value={requirement.title}
                onChange={(event) =>
                  setRequirement({ ...requirement, title: event.target.value })
                }
                placeholder="Requirement title"
                aria-label="Requirement title"
              />
              <Input
                value={requirement.category}
                onChange={(event) =>
                  setRequirement({
                    ...requirement,
                    category: event.target.value,
                  })
                }
                placeholder="Category"
                aria-label="Category"
              />
              <Input
                value={requirement.module_key}
                onChange={(event) =>
                  setRequirement({
                    ...requirement,
                    module_key: event.target.value,
                  })
                }
                placeholder="Module"
                aria-label="Module"
              />
              <Input
                value={requirement.description}
                onChange={(event) =>
                  setRequirement({
                    ...requirement,
                    description: event.target.value,
                  })
                }
                placeholder="Description"
                aria-label="Description"
              />
            </div>
            <Button
              className="mt-2"
              disabled={
                command.isPending ||
                Object.values(requirement).some((value) => value.length < 2)
              }
              onClick={() =>
                command.mutate(() =>
                  api.createCatalogueRequirement(requirement),
                )
              }
            >
              Create draft requirement
            </Button>
          </div>
        ) : null}
      </Card>
      <Card>
        <h2 className="font-semibold">Evidence mapping review</h2>
        <p className="mt-1 text-sm text-muted">
          Confirmation records a human-reviewed relationship only. It does not
          establish compliance or advance workflow.
        </p>
        {canPropose ? (
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <Input
              value={mapping.requirement_id}
              onChange={(event) =>
                setMapping({ ...mapping, requirement_id: event.target.value })
              }
              placeholder="Approved requirement UUID"
              aria-label="Requirement UUID"
            />
            <Input
              value={mapping.application_id}
              onChange={(event) =>
                setMapping({ ...mapping, application_id: event.target.value })
              }
              placeholder="Application UUID"
              aria-label="Application UUID"
            />
            <Input
              value={mapping.document_id}
              onChange={(event) =>
                setMapping({ ...mapping, document_id: event.target.value })
              }
              placeholder="Private document UUID"
              aria-label="Document UUID"
            />
            <Input
              value={mapping.document_version_id}
              onChange={(event) =>
                setMapping({
                  ...mapping,
                  document_version_id: event.target.value,
                })
              }
              placeholder="Exact document version UUID"
              aria-label="Document version UUID"
            />
            <Input
              value={mapping.explanation}
              onChange={(event) =>
                setMapping({ ...mapping, explanation: event.target.value })
              }
              placeholder="Review explanation"
              aria-label="Mapping explanation"
            />
          </div>
        ) : null}
        {canPropose ? (
          <Button
            className="mt-2"
            disabled={
              command.isPending ||
              Object.values(mapping).some((value) => value.length < 2)
            }
            onClick={() =>
              command.mutate(() => api.proposeRequirementMapping(mapping))
            }
          >
            Propose mapping
          </Button>
        ) : null}
        <div className="mt-3 space-y-2">
          {mappings.data?.map((item) => (
            <div className="rounded border p-3 text-sm" key={item.id}>
              <div className="flex flex-wrap justify-between gap-2">
                <span>
                  Requirement {item.requirement_id} · evidence{" "}
                  {item.document_version_id}
                </span>
                <Badge
                  tone={
                    item.status === "CONFIRMED"
                      ? "success"
                      : item.status === "REJECTED"
                        ? "danger"
                        : "warning"
                  }
                >
                  {item.status}
                </Badge>
              </div>
              <p className="mt-1 text-muted">{item.explanation}</p>
              {item.reviewed_at ? (
                <p className="text-xs text-muted">
                  Reviewed {new Date(item.reviewed_at).toLocaleString()}{" "}
                  {item.review_reason ? `· ${item.review_reason}` : ""}
                </p>
              ) : null}
              <Button
                className="mt-2"
                variant="outline"
                onClick={() => setSelectedMapping(item.id)}
              >
                View audit history
              </Button>
              {canReviewMappings && item.status === "PROPOSED" ? (
                <span className="mt-2 inline-flex gap-2">
                  <Button onClick={() => action(item.id, "mapping", "confirm")}>
                    Confirm
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => action(item.id, "mapping", "reject", true)}
                  >
                    Reject
                  </Button>
                </span>
              ) : null}
            </div>
          ))}
          {mappings.data?.length === 0 ? (
            <p className="text-sm text-muted">
              No mappings in your authorized scope.
            </p>
          ) : null}
        </div>
        {selectedMapping ? (
          <div className="mt-3 border-t pt-3">
            <h3 className="text-sm font-medium">Mapping audit history</h3>
            {history.isLoading ? (
              <p className="text-sm text-muted">Loading history…</p>
            ) : null}
            {history.isError ? (
              <Alert>
                Unable to load mapping history.
                <Button
                  className="ml-2"
                  variant="outline"
                  onClick={() => void history.refetch()}
                >
                  Retry
                </Button>
              </Alert>
            ) : null}
            {history.data?.map((event, index) => (
              <p
                className="text-xs text-muted"
                key={`${event.action}-${index}`}
              >
                {event.action} · {new Date(event.created_at).toLocaleString()}{" "}
                {event.reason ? `· ${event.reason}` : ""}
              </p>
            ))}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
