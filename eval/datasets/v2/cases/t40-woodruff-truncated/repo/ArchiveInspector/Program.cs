using System.IO.Compression;
using System.Text.Json;

using var archive = ZipFile.OpenRead("inputs/incoming.zip");
var entry = archive.GetEntry("inventory.json")
    ?? throw new InvalidDataException("inventory entry not found");
using var contents = entry.Open();
using var document = JsonDocument.Parse(contents);
Console.WriteLine(document.RootElement.GetProperty("total").GetInt32());
