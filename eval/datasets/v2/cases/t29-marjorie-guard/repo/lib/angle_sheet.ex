defmodule AngleSheet do
  def totals(a, b, c, d, e, f, g) do
    a
  end

  def choose(value) when String.downcase(value) == "east", do: :east
  def choose(_value), do: :other
end
