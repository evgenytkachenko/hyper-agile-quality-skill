/** Owner IDs are required strings. An absent principal cannot equal an owner. */
export function canReadLab(principal: string | undefined, owner: string): boolean {
  return principal === owner;
}
