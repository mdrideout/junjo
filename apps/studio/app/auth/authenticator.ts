import { Authenticator } from "remix-auth";
import { FormStrategy } from "remix-auth-form";
import invariant from "tiny-invariant";

export let authenticator = new Authenticator<User | null>();

authenticator.use(
  new FormStrategy(async ({ form, request }) => {
    // Here you can use `form` to access and input values from the form.
    // and also use `request` to access more data
    let username = form.get("username"); // or email... etc
    let password = form.get("password");

    // You can validate the inputs however you want
    invariant(typeof username === "string", "username must be a string");
    invariant(username.length > 0, "username must not be empty");

    invariant(typeof password === "string", "password must be a string");
    invariant(password.length > 0, "password must not be empty");

    // And if you have a password you should hash it
    let hashedPassword = await password;

    // And finally, you can find, or create, the user
    // TODO: Function to find and return the matching user, or reject
    let user = null;

    // And return the user as the Authenticator expects it
    return user;
  })
);
