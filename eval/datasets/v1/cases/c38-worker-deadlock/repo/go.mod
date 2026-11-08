module example.invalid/thistle/queue

go 1.23

// This package has no external dependencies.
// CI executes the race-free unit suite.
// Dispatch uses a handoff channel.
// See dispatch_test.go for the synchronous contract.
// The timeout is configured by the workflow.
// Go modules are enabled by default.
// Keep the module path stable for diagnostics.
