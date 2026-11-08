import { useQuery } from "@tanstack/react-query";

import { IS_REPLAY } from "../../lib/api/mode";
import { fetchHealth, healthQueryKey } from "./api";

export function useHealth() {
  return useQuery({
    queryKey: healthQueryKey,
    queryFn: fetchHealth,
    refetchInterval: 15_000,
    // Nothing runs behind the replay build, so there is no health to check.
    enabled: !IS_REPLAY,
  });
}
