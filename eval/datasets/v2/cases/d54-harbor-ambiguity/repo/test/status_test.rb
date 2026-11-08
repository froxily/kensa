require "minitest/autorun"
require "harbor"

class StatusTest < Minitest::Test
  def test_name_length; assert_equal 6, "harbor".length; end
  def test_name_prefix; assert "harbor".start_with?("har"); end
  def test_name_suffix; assert "harbor".end_with?("bor"); end
  def test_name_case; assert_equal "HARBOR", "harbor".upcase; end
  def test_split_pair; assert_equal 2, "a,b".split(",").length; end
  def test_strip_space; assert_equal "a", " a ".strip; end
  def test_join_names; assert_equal "a-b", ["a", "b"].join("-"); end
  def test_empty_value; assert_empty ""; end
  def test_decimal; assert_equal 4, "4".to_i; end
  def test_replace; assert_equal "a_b", "a-b".tr("-", "_"); end
  def test_first_char; assert_equal "h", "harbor"[0]; end
  def test_include; assert_includes "harbor", "ar"; end
  def test_ready_flag
    path = ENV.fetch("HARBOR_FLAG_FILE", "")
    assert Harbor.ready?(path)
  end
end
