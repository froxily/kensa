require "minitest/autorun"
require_relative "../lib/kestrel_settings"

class StartupTest < Minitest::Test
  def test_banner_includes_region
    assert_match(/region:/, KestrelSettings.banner)
  end
end
