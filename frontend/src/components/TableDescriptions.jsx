import DescribeModal from "./DescribeModal";

/**
 * TableDescriptions component rendered on the Schema tab below the ER diagram.
 * Uses the exact same design and logic as DescribeModal.
 */
export default function TableDescriptions({ tables, schemaVersion, onDescriptionsChanged }) {
  return (
    <div className="mt-8">
      <DescribeModal
        tables={tables}
        schemaVersion={schemaVersion}
        isModal={false}
        isOpen={true}
        onDescriptionsChanged={onDescriptionsChanged}
      />
    </div>
  );
}
