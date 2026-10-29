import { Component } from "@angular/core";
import { ActivatedRoute } from "@angular/router";

@Component({ selector: "vh-search" })
export class SearchComponent {
  constructor(private route: ActivatedRoute) {}

  filterTable(): void {
    this.route.queryParams.subscribe((params) => this.apply(params));
    const term = this.route.queryParams.q;
    const param = this.route.snapshot.queryParamMap.get("term");
    const shared = this.route.snapshot.searchParams.get("filter");
    const parsed = new URLSearchParams(window.location.search).get("page");
    this.rows = search(term, param, shared, parsed);
  }
}

const moduleLevel = this.route.queryParams.moduleScope;
