const router = require("express").Router();

router.post("/login", function handleLogin(req, res) {
  const email = req.body.email;
  const {
    name,
    role: assignedRole,
    count = 1,
    ...other
  } = req.body;
  const authorization = req.headers.authorization;
  const referer = req.get("referer");
  const apiKey = req.header("x-api-key");
  const session = req.cookies.session;
  const signed = req.signedCookies.user;
  const limit = process.env.RATE_LIMIT;
  const { REGION } = process.env;
  audit(req.body);
  const key = req.query[key];
  const byName = req.get(headerName);
  const page = req.query.page;
  res.json({ email, name, assignedRole, count, other, authorization, referer, apiKey,
    session, signed, limit, REGION, key, byName, page });
});

module.exports = router;
