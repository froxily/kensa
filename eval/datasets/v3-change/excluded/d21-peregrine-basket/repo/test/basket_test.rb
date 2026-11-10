require "minitest/autorun"
require "basket"

class BasketTest < Minitest::Test
  def test_delivery_at_qualifying_boundary
    assert_equal 7, Peregrine::Basket.delivery_fee(50)
  end
end
