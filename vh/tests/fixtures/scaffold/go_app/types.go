package app

type Inner struct {
	Note string
}

type Base struct {
	Tenant string
}

type Login struct {
	Base
	User   string `json:"username"`
	Email  string
	Inner  Inner
	Pass   string `json:"-"`
	A, B   string
	Anon   struct {
		Deep string
	}
	Nested map[string][]Inner
}

type Other struct {
	Secret string `json:"secret"`
}
