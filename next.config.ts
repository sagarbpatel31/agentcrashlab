import { withEve } from "eve/next";
export default withEve({
  devIndicators: false,
  logging: { incomingRequests: false },
});
