const express = require("express");
const app = express();

/*
 * req.query.ghost is inside a block comment and must produce no row.
 */
const marker = "*/*";

function searchHandler(req, res) {
  const q = req.query.q;
  res.json({ q });
}

app.get("/users/:id", searchHandler);
app.get("http://host:8080/status", searchHandler);

this.displayAllocations = (req, res, next) => {
  const userId = req.params.userId;
  const rows = db.rows(userId);
  res.json(rows);
};

module.exports = { app, searchHandler };
