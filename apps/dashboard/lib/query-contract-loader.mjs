export async function resolve(specifier, context, nextResolve) {
  if (specifier === "./db") {
    return nextResolve("./db.ts", context);
  }
  if (specifier === "./analytics-rollout") {
    return nextResolve("./analytics-rollout.ts", context);
  }

  return nextResolve(specifier, context);
}
