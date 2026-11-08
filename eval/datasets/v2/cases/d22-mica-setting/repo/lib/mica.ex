defmodule Mica do
  def namespace, do: System.fetch_env!("MICA_NAMESPACE")
  def normalize(value), do: String.trim(value)
end
