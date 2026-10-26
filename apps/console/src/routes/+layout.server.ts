export const load = ({ locals }: { locals: App.Locals }) => ({
  principal: locals.session?.principal ?? null,
});
