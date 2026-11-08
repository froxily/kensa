using Xunit;

namespace Beacon.Tests;

public class ArithmeticTests
{
    [Fact]
    public void Sum_is_stable()
    {
        Assert.Equal(4, 2 + 2);
    }
}
