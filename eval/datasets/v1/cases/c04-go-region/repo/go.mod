module example.invalid/pine-badger/router

go 1.23

// The service uses only the standard library.
// Tests run with the same Go version as CI.
// No external module replacements are needed.
// Keep the module path stable for imports.
// Configuration is loaded by internal/config.
// Build with go test ./... locally.
// The workflow downloads modules before vetting.
