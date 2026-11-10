import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  createInvestigation,
  getChanges,
  getHistory,
  saveResolution,
  decideInvestigation,
  getDocument,
  getInvestigation,
  listEvents,
  listInvestigations,
  listSamples,
  lookupGitHub,
  queryKeys,
  retryInvestigation,
  streamUrl,
} from "./api";
import { isTerminal, type AgentEvent, type DecisionBody, type InvestigationStatus } from "./types";

export function useInvestigations(limit = 20) {
  return useQuery({
    queryKey: queryKeys.list(limit),
    queryFn: () => listInvestigations(limit),
    // Keep the list fresh while something is still running.
    refetchInterval: (query) =>
      query.state.data?.items.some((i) => !isTerminal(i.status)) ? 3_000 : false,
  });
}

export function useInvestigation(id: string) {
  return useQuery({
    queryKey: queryKeys.detail(id),
    queryFn: () => getInvestigation(id),
    // Fallback polling in case the live stream is unavailable.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && !isTerminal(status) ? 5_000 : false;
    },
  });
}

export function useDocument(id: string, documentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.document(id, documentId ?? ""),
    queryFn: () => getDocument(id, documentId ?? ""),
    enabled: documentId !== undefined,
    staleTime: Infinity,
  });
}

export function useSamples() {
  return useQuery({ queryKey: queryKeys.samples, queryFn: listSamples, staleTime: Infinity });
}

export function useCreateInvestigation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createInvestigation,
    onSuccess: () => client.invalidateQueries({ queryKey: ["investigations", "list"] }),
  });
}

export function useRetryInvestigation(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => retryInvestigation(id),
    onSuccess: () => client.invalidateQueries({ queryKey: ["investigations"] }),
  });
}

/** Looks up a GitHub repository, run or job URL (read-only; no investigation is created). */
export function useGitHubLookup() {
  return useMutation({ mutationFn: lookupGitHub });
}

/** Records an approve/reject decision; the server then resumes the paused agent run. */
export function useDecideInvestigation(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: DecisionBody) => decideInvestigation(id, body),
    onSettled: () => client.invalidateQueries({ queryKey: ["investigations"] }),
  });
}

function mergeEvents(current: AgentEvent[], incoming: AgentEvent[]): AgentEvent[] {
  const bySeq = new Map(current.map((e) => [e.seq, e]));
  for (const event of incoming) bySeq.set(event.seq, event);
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
}

/**
 * The agent timeline: loads past events over REST, then follows the server-sent event stream
 * until the investigation finishes. Status changes refresh the investigation query.
 */
export function useAgentEvents(id: string, status: InvestigationStatus | undefined) {
  const client = useQueryClient();
  const initial = useQuery({ queryKey: queryKeys.events(id), queryFn: () => listEvents(id) });
  const [live, setLive] = useState<AgentEvent[]>([]);
  const terminal = status === undefined || isTerminal(status);
  const lastSeq = initial.data?.at(-1)?.seq ?? 0;

  useEffect(() => {
    if (terminal || !initial.isSuccess || typeof EventSource === "undefined") return undefined;
    const source = new EventSource(streamUrl(id, lastSeq));
    const refresh = () => {
      void client.invalidateQueries({ queryKey: queryKeys.detail(id) });
      void client.invalidateQueries({ queryKey: ["investigations", "list"] });
    };
    source.addEventListener("agent_event", (message) => {
      const event = JSON.parse((message as MessageEvent<string>).data) as AgentEvent;
      setLive((current) => mergeEvents(current, [event]));
    });
    source.addEventListener("status", refresh);
    source.addEventListener("end", () => {
      source.close();
      refresh();
    });
    return () => {
      source.close();
    };
    // lastSeq is read once when the stream opens; reconnects resume via Last-Event-ID.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, terminal, initial.isSuccess, client]);

  // After the run ends, reload so the timeline holds the server's full, ordered history.
  useEffect(() => {
    if (terminal && live.length > 0) {
      void client.invalidateQueries({ queryKey: queryKeys.events(id) });
    }
  }, [terminal, live.length, id, client]);

  return { ...initial, events: mergeEvents(initial.data ?? [], live) };
}

export function useChanges(id: string) {
  return useQuery({ queryKey: queryKeys.changes(id), queryFn: () => getChanges(id) });
}
export function useHistory(id: string) {
  return useQuery({ queryKey: queryKeys.history(id), queryFn: () => getHistory(id) });
}
export function useSaveResolution(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (summary: string) => saveResolution(id, summary),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.history(id) }),
  });
}
