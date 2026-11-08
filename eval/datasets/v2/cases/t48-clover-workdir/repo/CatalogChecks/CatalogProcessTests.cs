using System.Diagnostics;
using NUnit.Framework;

public class CatalogProcessTests {
    [Test]
    public void ToolReportsVersion() {
        var info = new ProcessStartInfo("dotnet", "--version") {
            WorkingDirectory = Environment.GetEnvironmentVariable("CLOVER_RUN_DIR")!,
            UseShellExecute = false
        };
        using var process = Process.Start(info)!;
        process.WaitForExit();
        Assert.That(process.ExitCode, Is.Zero);
    }
}
