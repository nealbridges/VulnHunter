package app

import "encoding/json"

func handleSearch(r *http.Request) {
	term := r.URL.Query().Get("term")
	page := r.DefaultQuery("page", "1")
	sort := r.QueryParam("sort")
	raw := r.Query("raw")
	id := r.PathValue("id")
	pid := r.Param("pid")
	uid := chi.URLParam(r, "uid")
	mid := mux.Vars(r)["mid"]
	auth := r.Header.Get("Authorization")
	key := r.GetHeader("X-Key")
	name := r.FormValue("name")
	post := r.PostFormValue("post")
	multi := r.PostForm("multi")
	home := os.Getenv("HOME")
	secret := os.LookupEnv("SECRET")
	flag.String("verbose", false, "")
	flag.IntVar(&count, "count", 1, "")
	cmd.Flags().StringP("out", "o", "", "")
	cmd.PersistentFlags().BoolVarP(&debug, "debug", "d", false, "")
	var login Login
	json.NewDecoder(r.Body).Decode(&login)
	var form Login
	r.ShouldBindJSON(&form)
	var unknown Missing
	r.Bind(&unknown)
}

func other() {
	v := Other{}
	_ = v
}
}
