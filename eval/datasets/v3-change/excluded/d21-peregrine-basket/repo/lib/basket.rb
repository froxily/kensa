module Peregrine
  class Basket
    def self.delivery_fee(subtotal)
      subtotal >= 50 ? 0 : 7
    end
  end
end
