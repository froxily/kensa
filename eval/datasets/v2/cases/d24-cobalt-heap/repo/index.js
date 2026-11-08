const records = [];
for (let batch = 1; batch <= 100; batch++) {
  for (let row = 0; row < 2000; row++) {
    records.push({ id: `${batch}-${row}`, text: "x".repeat(1024), title: "y".repeat(512), tag: "z".repeat(512), note: "w".repeat(1024) });
  }
  console.log(`indexed batch ${batch}: ${records.length} records`);
}
console.log(`index complete: ${records.length} records`);
