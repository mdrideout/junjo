package auth

import (
	"context"
	"junjo-server/db"
	"junjo-server/db_gen"
)

// DbHasUsers checks if any users exist and returns a boolean.
func DbHasUsers(ctx context.Context) (bool, error) {
	queries := db_gen.New(db.DB)
	count, err := queries.CountUsers(ctx)
	if err != nil {
		return false, err
	}
	return count > 0, nil
}

func CreateUser(ctx context.Context, email string, password string) error {
	queries := db_gen.New(db.DB)
	_, err := queries.CreateUser(ctx, db_gen.CreateUserParams{
		Email:        email,
		PasswordHash: password,
	})
	if err != nil {
		return err
	}
	return nil
}

func GetUserByEmail(ctx context.Context, email string) (db_gen.User, error) {
	queries := db_gen.New(db.DB)
	user, err := queries.GetUserByEmail(ctx, email)
	if err != nil {
		return db_gen.User{}, err
	}
	return user, nil
}

func ListUsers(ctx context.Context) ([]db_gen.ListUsersRow, error) {
	queries := db_gen.New(db.DB)
	users, err := queries.ListUsers(ctx)
	if err != nil {
		return nil, err
	}
	return users, nil
}

func DeleteUser(ctx context.Context, id int64) error {
	queries := db_gen.New(db.DB)
	err := queries.DeleteUser(ctx, id)
	if err != nil {
		return err
	}
	return nil
}
