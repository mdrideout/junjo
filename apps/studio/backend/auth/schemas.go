package auth

type User struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}
