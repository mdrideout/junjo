from app.workflows.handle_message.graph import create_handle_message_graph


def main():
    """
    Demonstration visualization options for the sample workflow graph.
    """
    graph_dot_notation_str = create_handle_message_graph().to_dot_notation()
    print("Graph DOT Notation:\n", graph_dot_notation_str)

    # Export graphviz assets
    create_handle_message_graph().export_graphviz_assets()

    print("\n\nCheck `graphviz_out` folder for visualizations.\n")


if __name__ == "__main__":
    main()
