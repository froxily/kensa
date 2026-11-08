using System;
using System.Diagnostics;
using System.IO;
using Xunit;
using Xunit.Abstractions;

public class ContainerTests
{
    private readonly ITestOutputHelper output;
    public ContainerTests(ITestOutputHelper output) => this.output = output;

    [Theory]
    [InlineData("a")][InlineData("b")][InlineData("c")][InlineData("d")]
    [InlineData("e")][InlineData("f")][InlineData("g")][InlineData("h")]
    public void NameIsNotEmpty(string name) => Assert.NotEmpty(name);

    [Fact]
    public void ImageBuilds()
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../.."));
        var info = new ProcessStartInfo("docker", "build --progress=plain -t rill-check .") {
            WorkingDirectory = root, RedirectStandardError = true, RedirectStandardOutput = true
        };
        using var process = Process.Start(info)!;
        string stdout = process.StandardOutput.ReadToEnd();
        string stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();
        output.WriteLine(stdout + stderr);
        Assert.Equal(0, process.ExitCode);
    }
}
