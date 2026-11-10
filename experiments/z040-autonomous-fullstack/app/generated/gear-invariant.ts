export function canAdvanceGearItem(record, parent) {
  if (record.status === "stashed") {
    return parent !== null;
  }
  if (record.status === "inspected") {
    return record.usageHours >= 1 && record.usageHours <= 2000;
  }
  if (record.status === "retired") {
    return false;
  }
  return false;
}