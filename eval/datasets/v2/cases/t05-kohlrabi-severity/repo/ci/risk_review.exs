Code.require_file("../lib/risk_classifier.ex", __DIR__)

defmodule RiskTest do
  def a_test, do: (:info = RiskClassifier.severity("queued"))
  def b_test, do: (:info = RiskClassifier.severity("started"))
  def c_test, do: (:info = RiskClassifier.severity("ready"))
  def d_test, do: (:info = RiskClassifier.severity("active"))
  def e_test, do: (:info = RiskClassifier.severity("paused"))
  def f_test, do: (:info = RiskClassifier.severity("waiting"))
  def g_test, do: (:info = RiskClassifier.severity("retrying"))
  def h_test, do: (:info = RiskClassifier.severity("complete"))
  def i_test, do: (:info = RiskClassifier.severity("idle"))
  def j_test, do: (:info = RiskClassifier.severity("pending"))
  def k_test, do: (:info = RiskClassifier.severity("received"))
  def l_test, do: (:info = RiskClassifier.severity("stored"))
  def m_test, do: (:info = RiskClassifier.severity("sent"))
  def denial_test do
    text = "package push denied: permission denied"
    IO.puts("classifying: #{text}")
    :error = RiskClassifier.severity(text)
  end
end

if :eunit.test(RiskTest, [:verbose]) != :ok, do: System.halt(1)
