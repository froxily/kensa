for (int window = 1; window <= 24; window++)
{
    Console.WriteLine($"Loaded ledger window {window:D2}");
}
Console.WriteLine("Waiting for the aggregation interval");
await Task.Delay(TimeSpan.FromSeconds(90));
Console.WriteLine("Aggregation complete");
