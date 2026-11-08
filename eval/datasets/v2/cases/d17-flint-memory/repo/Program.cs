using System;
using System.Collections.Generic;

var chunks = new List<byte[]>();
for (var i = 0; i < 100; i++)
{
    chunks.Add(new byte[1024 * 1024]);
}
Console.WriteLine($"Snapshot chunks: {chunks.Count}");
