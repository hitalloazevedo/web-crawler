import json

def clean_link_json(input_filename, output_filename):
    # Extensions to identify "images"
    img_exts = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.ico')

    def is_image(url):
        # Remove query parameters like ?v=1 before checking extension
        clean_url = url.split('?')[0].lower()
        return clean_url.endswith(img_exts)

    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        cleaned_data = {}

        for parent_url, children_links in data.items():
            # SKIP the entire entry if the PARENT is an image
            if is_image(parent_url):
                continue
            
            # FILTER the list if any CHILD is an image
            filtered_children = [
                link for link in children_links 
                if not is_image(link)
            ]
            
            cleaned_data[parent_url] = filtered_children

        # Write to a new file
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
            
        print(f"Cleanup complete. Results saved to '{output_filename}'.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Example usage:
    clean_link_json('graph.json', 'graph-no-images.json')