import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { forgetRepository, listRepositories, syncRepository, trackRepository } from "./api";
export function useTracking() {
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["tracking"] });
    void client.invalidateQueries({ queryKey: ["analytics"] });
  };
  return {
    repositories: useQuery({
      queryKey: ["tracking"],
      queryFn: listRepositories,
      refetchInterval: (q) => (q.state.data?.some((r) => r.syncing) ? 5000 : false),
    }),
    track: useMutation({ mutationFn: trackRepository, onSuccess: refresh }),
    sync: useMutation({ mutationFn: syncRepository, onSuccess: refresh }),
    forget: useMutation({
      mutationFn: ({ id, confirm }: { id: string; confirm: string }) =>
        forgetRepository(id, confirm),
      onSuccess: refresh,
    }),
  };
}
