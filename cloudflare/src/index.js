import { DurableObject } from "cloudflare:workers";

import { MCPApplication } from "./app.js";

export class MaintenanceState extends DurableObject {
  async fetch(request) {
    return new MCPApplication(this.ctx.storage, this.env).handle(request);
  }
}

export default {
  async fetch(request, env) {
    const state = env.MAINTENANCE_STATE.getByName("industrial-maintenance");
    return state.fetch(request);
  },
};
