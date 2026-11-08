using Xunit;

namespace Lumen;

public class MessageTests
{
    [Fact]
    public void MissingRegionNamesSetting()
    {
        Assert.Equal("Missing variable: REGION_CODE", Messages.MissingRegion());
    }
}
