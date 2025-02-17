/**
 * User class
 *
 * This class is used to represent the user object in the application.
 */
class User {
  id: string;
  email: string;
  name: string;

  constructor(id: string, email: string, name: string) {
    this.id = id;
    this.email = email;
    this.name = name;
  }
}
