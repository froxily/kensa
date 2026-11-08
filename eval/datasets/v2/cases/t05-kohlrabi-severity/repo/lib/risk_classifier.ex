defmodule RiskClassifier do
  def severity(text) do
    if String.contains?(text, "denied"), do: :warning, else: :info
  end
end
