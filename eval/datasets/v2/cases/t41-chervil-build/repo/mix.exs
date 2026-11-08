defmodule ChervilImage.MixProject do
  use Mix.Project
  def project, do: [app: :chervil_image, version: "0.1.0", elixir: "~> 1.16"]
  def application, do: [extra_applications: [:logger]]
end
