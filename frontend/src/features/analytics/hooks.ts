import { useQuery } from "@tanstack/react-query";
import { getDashboard, type Filters } from "./api";
export function useDashboard(filters: Filters) {
  return useQuery({ queryKey: ["analytics", filters], queryFn: () => getDashboard(filters) });
}
