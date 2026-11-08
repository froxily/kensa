defmodule EmberTest do
  use ExUnit.Case

  test "counts only active records" do
    assert Ember.count_active([%{active: true}, %{active: false}]) == 1
  end
end
