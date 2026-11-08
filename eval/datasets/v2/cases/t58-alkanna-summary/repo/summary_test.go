package summary

import (
    "strings"
    "testing"
)

func summarize(problems []string) string {
    return strings.TrimSpace(problems[len(problems)-1])
}

func TestSummary(t *testing.T) {
    cases := []struct{ name string; input []string; want string }{
        {"one", []string{"alpha"}, "alpha"},
        {"two", []string{"beta"}, "beta"},
        {"three", []string{"gamma"}, "gamma"},
        {"four", []string{"delta"}, "delta"},
        {"five", []string{"epsilon"}, "epsilon"},
        {"six", []string{"zeta"}, "zeta"},
        {"registry", []string{"permission denied while trying to connect to the Docker daemon", "stale build output"}, "permission denied while trying to connect to the Docker daemon"},
    }
    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            if got := summarize(tc.input); got != tc.want { t.Errorf("got %q, want %q", got, tc.want) }
        })
    }
}
