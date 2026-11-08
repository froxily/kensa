defmodule AngleSheet.MixProject do
  use Mix.Project
  def project, do: [app: :angle_sheet, version: "0.1.0", elixir: "~> 1.14"]
  def application, do: [extra_applications: [:logger]]
end
